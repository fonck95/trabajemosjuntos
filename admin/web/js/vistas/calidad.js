// Calidad de datos: coincidencias por nombre, conflictos de cédula, solicitudes de los titulares, situaciones
// reportadas, lugares sin punto y nombres nuevos. Todo dato de la base pasa por `html` (escapado).
import { api } from '../api.js';
import { refrescarInsignias } from '../app.js';
import { SITUACIONES } from '../modelo.js';
import { $, aviso, avisoError, confirmar, datosForm, dialogo, fecha, html, montar, num, titulo } from '../ui.js';
import { elegirPunto } from './comunes.js';
import { url } from '../base.js';

const PESTANAS = [['coincidencias', 'Coincidencias por revisar'], ['conflictos', 'Conflictos de cédula'],
  ['solicitudes', 'Solicitudes de titulares'], ['situaciones', 'Situaciones reportadas'], ['lugares', 'Barrios y veredas'],
  ['sin', 'Lugares sin reconocer']];
const MOTIVOS_COINCIDENCIA = { homonimo: 'Mismo nombre, otra ficha', variante: 'Nombre parecido, misma ficha',
  cruce_cedula: 'Base con cédula', nombre_telefono: 'Fila sin cédula', alta_simultanea: 'Alta simultánea', reporte: 'Reportado' };
const MOTIVOS_CONFLICTO = { nombre_distinto: 'Misma cédula, otro nombre', cedula_anterior: 'Cédula anterior de una ficha',
  posible_digitacion: 'Posible error de digitación', dictada: 'Cédula dictada al consultor' };
const FUENTES = { cedulas: 'Base con cédula', planilla: 'Planilla de campo', consultor: 'Consultor', tramites: 'Trámites' };
const TIPOS_SOLICITUD = { consulta: 'Consulta', correccion: 'Corrección', supresion: 'Supresión', revocatoria: 'Revocatoria',
  otro: 'Otro', registro: 'Pedido de registro' };
const ESTADOS_SOLICITUD = { pendiente: 'Pendiente', en_tramite: 'En trámite', resuelta: 'Resuelta', rechazada: 'Rechazada' };

export async function vistaCalidad(el, { q }) {
  let pestana = PESTANAS.some(([k]) => k === q.get('p')) ? q.get('p') : 'coincidencias';
  montar(el, html`
    <div class="cabecera"><div><h1>Calidad de datos</h1><div class="sub">Lo que la máquina no decide sola: usted confirma, y la base queda más completa.</div></div>
      <div class="acciones"><button class="btn" id="regeo">Recalcular ubicaciones</button></div></div>
    <div class="pestanas" role="tablist">
      ${PESTANAS.map(([k, t]) => html`<button role="tab" data-tab="${k}" aria-selected="${k === pestana}">${t}</button>`)}
    </div>
    <div id="cuerpo"></div>`);

  // Cada carga lleva un turno: si se cambió de pestaña mientras llegaba, no pinta encima de la nueva
  let turno = 0;
  const vigente = (t) => t === turno && el.isConnected;
  const VISTAS = { coincidencias, conflictos, solicitudes, situaciones, lugares, sin: sinReconocer };

  async function pintar() {
    for (const b of el.querySelectorAll('[data-tab]')) b.setAttribute('aria-selected', b.dataset.tab === pestana);
    history.replaceState({}, '', url(`/calidad?p=${pestana}`));
    const c = $('#cuerpo', el);
    montar(c, html`<div class="cargando"><div class="giro"></div></div>`);
    c.onclick = null;
    c.onchange = null;
    const t = ++turno;
    try { await VISTAS[pestana](c, t); } catch (err) { if (vigente(t)) montar(c, html`<div class="aviso-legal">${err.message}</div>`); }
  }
  // Vuelve a cargar la pestaña después de una acción, solo si el usuario sigue en ella
  const recargar = (fn, nombre, c) => { if (pestana === nombre && el.isConnected) fn(c, ++turno); };

  const lado = (p, otro, rotulo) => {
    const tb = new Set((otro?.nombre || '').split(/\s+/));
    const marcado = html`${(p.nombre || '').split(/\s+/).map((w) => (tb.has(w) ? html`<span class="igual">${w}</span> ` : html`${w} `))}`;
    return html`<div class="lado"><span class="sec">${rotulo}</span><b><a href="/personas/${p.id}" data-ruta>${marcado}</a></b>
      <dl><dt>Cédula</dt><dd>${p.cedula || '—'}</dd><dt>Teléfono</dt><dd>${[p.telefono, p.telefono2].filter(Boolean).join(', ') || '—'}</dd>
      <dt>Lugar</dt><dd>${titulo(p.lugar || '') || '—'}</dd><dt>Dirección</dt><dd>${p.direccion || '—'}</dd>
      ${p.edad ? html`<dt>Edad</dt><dd>${p.edad} · ${p.sexo || ''}</dd>` : ''}${p.tramites ? html`<dt>Trámites</dt><dd>${p.tramites}</dd>` : ''}
      ${p.listas ? html`<dt>Listas</dt><dd>${p.listas}</dd>` : ''}${p.completitud != null ? html`<dt>Completitud</dt><dd>${p.completitud}%</dd>` : ''}</dl></div>`;
  };

  async function coincidencias(c, mio) {
    const lista = await api.get('/api/coincidencias');
    if (!vigente(mio)) return;
    if (!lista.length) { montar(c, html`<div class="tarjeta vacio"><b>Nada pendiente</b>Todas las coincidencias por nombre están resueltas.</div>`); return; }
    // Pares y, como en el panel y la insignia, personas por revisar (`ids`: una por par)
    const cuenta = (ids) => {
      const personas = new Set(ids).size;
      return `${num(ids.length)} ${ids.length === 1 ? 'par' : 'pares'} de fichas con nombres parecidos (${num(personas)} ${personas === 1 ? 'persona' : 'personas'} por revisar).`;
    };
    const rotulo = (x, izquierda) => {
      if (x.detalle.homonimo) return 'Mismo nombre, otra ficha';
      if (x.detalle.variante) return 'Nombre parecido, misma ficha';
      if (!izquierda) return 'Ficha existente';
      return MOTIVOS_COINCIDENCIA[x.motivo] || 'Base con cédula';
    };
    montar(c, html`<p class="sec"><span id="cuenta-pares">${cuenta(lista.map((x) => x.persona.id))}</span> Si son la misma persona, se unen: nada se pierde (lo distinto queda como dato alterno). Por defecto se conserva la ficha que tiene cédula.</p>
      <div style="display:flex;flex-direction:column;gap:12px">${lista.map((x) => html`<div class="tarjeta" data-c="${x.id}" data-p="${x.persona.id}"><div class="par">
        ${lado(x.persona, x.candidato, rotulo(x, true))}
        <div class="medio"><span class="puntaje">${Math.round(x.puntaje * 100)}%</span>
          <span class="sec" style="text-align:center">${x.detalle.palabras ? `${x.detalle.palabras} palabras` : ''}${x.detalle.telefono ? html`<br><span class="chip verde">mismo teléfono</span>` : ''}${x.detalle.correo ? html`<br><span class="chip verde">mismo correo</span>` : ''}</span>
          <label class="campo"><span>Conservar</span><select data-conservar><option value="">La que tiene cédula</option><option value="persona">La de la izquierda</option><option value="candidato">La de la derecha</option></select></label>
          <button class="btn chico primario" data-d="aceptar">Es la misma</button><button class="btn chico" data-d="rechazar">Son distintas</button></div>
        ${lado(x.candidato, x.persona, rotulo(x, false))}</div></div>`)}</div>`);
    c.onclick = async (e) => {
      const b = e.target.closest('[data-d]');
      if (!b) return;
      const t = b.closest('[data-c]');
      const conservar = t.querySelector('[data-conservar]')?.value || null;
      b.disabled = true;
      try {
        await api.post(`/api/coincidencias/${t.dataset.c}`, { decision: b.dataset.d, ...(conservar && b.dataset.d === 'aceptar' ? { conservar } : {}) });
        aviso(b.dataset.d === 'aceptar' ? 'Fichas unidas' : 'Marcadas como personas distintas');
        refrescarInsignias();
        // Unir reapunta o cierra en el servidor las demás coincidencias de esa ficha: se vuelve a pedir la lista
        if (b.dataset.d === 'aceptar') { recargar(coincidencias, 'coincidencias', c); return; }
        t.style.transition = 'opacity .25s'; t.style.opacity = 0;
        setTimeout(() => {
          t.remove();
          const r = $('#cuenta-pares', c);
          if (r) r.textContent = cuenta([...c.querySelectorAll('[data-c]')].map((x) => x.dataset.p));
        }, 260);
      } catch (err) {
        aviso(err.message, 'error'); b.disabled = false;
        if (err.estado === 404) recargar(coincidencias, 'coincidencias', c); // ya resuelta: la tarjeta sobra
      }
    };
  }

  async function conflictos(c, mio) {
    const lista = await api.get('/api/conflictos');
    if (!vigente(mio)) return;
    if (!lista.length) { montar(c, html`<div class="tarjeta vacio"><b>Sin conflictos de cédula</b>Ninguna fila trae una cédula que choque con la base.</div>`); return; }
    const fila = (r, x) => html`<div class="lado"><span class="sec">Fila · ${FUENTES[x.fuente] || x.fuente || ''}${r.fila ? ` · fila ${r.fila}` : ''}</span><b>${r.nombre || '—'}</b>
      <dl><dt>Cédula</dt><dd>${r.cedula || '—'}${r.cedula && r.tipo_documento ? ` (${r.tipo_documento})` : ''}</dd>
      ${x.cedula && x.cedula !== r.cedula ? html`<dt>En conflicto</dt><dd>${x.cedula}</dd>` : ''}
      ${r.cedula_digitada || r.cedula_repetida ? html`<dt>Escrita</dt><dd>${r.cedula_digitada || '—'} · repetida ${r.cedula_repetida || '—'}</dd>` : ''}
      <dt>Teléfonos</dt><dd>${(r.telefonos || []).join(', ') || '—'}</dd><dt>Dirección</dt><dd>${r.direccion || '—'}</dd>
      ${r.edad || r.fecha_nacimiento ? html`<dt>Edad</dt><dd>${r.fecha_nacimiento || r.edad} · ${r.sexo || ''}</dd>` : ''}</dl></div>`;
    const botones = (x) => {
      const aplicar = html`<button class="btn chico primario" data-r="aplicar">Aplicar</button>`;
      const descartar = html`<button class="btn chico" data-r="descartar">Descartar</button>`;
      if (x.motivo === 'posible_digitacion') return html`<button class="btn chico primario" data-r="corregir">Corregir cédula</button>${descartar}`;
      if (x.motivo === 'dictada' && x.duena) return html`<button class="btn chico primario" data-r="reportar">Reportar duplicado</button>${descartar}`;
      return html`${aplicar}${descartar}`;
    };
    const ayuda = {
      nombre_distinto: 'La cédula ya está en una ficha con otro nombre. «Aplicar» toma la fila como de esta persona (sin cambiar su cédula); si es otra persona, descártela.',
      cedula_anterior: 'La fila trae una cédula que esta ficha tuvo antes. «Aplicar» completa la ficha con la fila.',
      posible_digitacion: 'La cédula difiere en un dígito de otra, o la planilla trae dos cédulas distintas. Nunca se une: corrija la cédula con su motivo o descarte el aviso.',
      dictada: 'Cédula que el titular le dictó al consultor. «Aplicar» la asigna si sigue libre; si ya es de otra ficha, repórtelas como duplicado.',
    };
    montar(c, html`<p class="sec">${num(lista.length)} conflictos. Ninguno mezcla datos hasta que usted decida.</p>
      <div style="display:flex;flex-direction:column;gap:12px">${lista.map((x) => html`<div class="tarjeta" data-k="${x.id}">
        <header style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px"><span class="chip ambar">${MOTIVOS_CONFLICTO[x.motivo] || x.motivo}</span>
          ${x.puntaje_nombre != null ? html`<span class="sec">Parecido del nombre: ${Math.round(x.puntaje_nombre * 100)}%</span>` : ''}
          <span class="sec">${fecha(x.creado_en, true)}</span></header>
        <p class="sec" style="margin-top:0">${ayuda[x.motivo] || ''}</p>
        <div class="par">${fila(x.registro || {}, x)}
          <div class="medio">${botones(x)}</div>
          ${x.persona ? lado(x.persona, x.registro, 'Ficha') : html`<div class="lado"><span class="sec">Ficha</span><b>Ya no está activa</b></div>`}</div>
        ${x.duena ? html`<div class="par" style="margin-top:10px"><div></div><div class="medio"><span class="sec">Dueña de la cédula</span></div>${lado(x.duena, x.persona, 'Ficha con esa cédula')}</div>` : ''}
        ${x.otra_persona ? html`<div class="par" style="margin-top:10px"><div></div><div class="medio"><span class="sec">Cédula parecida</span></div>${lado(x.otra_persona, x.persona, 'Otra ficha')}</div>` : ''}
      </div>`)}</div>`);
    c.onclick = async (e) => {
      const b = e.target.closest('[data-r]');
      if (!b) return;
      const tarjeta = b.closest('[data-k]');
      const id = tarjeta.dataset.k;
      const resolver = async (cuerpo) => {
        await api.post(`/api/conflictos/${id}`, cuerpo);
        aviso('Conflicto resuelto');
        recargar(conflictos, 'conflictos', c);
      };
      if (b.dataset.r === 'corregir') { corregirCedula(lista.find((x) => String(x.id) === id), resolver); return; }
      if (b.dataset.r === 'aplicar' && !await confirmar('¿La fila es de esta persona? Se completará la ficha y lo distinto quedará como dato alterno.', { si: 'Aplicar' })) return;
      b.disabled = true;
      try { await resolver({ decision: b.dataset.r }); } catch (err) { avisoError(err); b.disabled = false; }
    };
  }

  function corregirCedula(x, resolver) {
    const sugerida = x.registro?.cedula_repetida || x.cedula || '';
    const { el: d, cerrar } = dialogo({ titulo: 'Corregir cédula',
      cuerpo: html`<form class="form" id="f-ced">
        <p class="sec ancho" style="margin:0">Escriba la cédula correcta dos veces. La cédula actual de la ficha (si tiene) pasa a sus cédulas anteriores.</p>
        <label class="campo"><span>Cédula correcta</span><input name="cedula" inputmode="numeric" autocomplete="off" required pattern="[0-9]{5,11}" value="${sugerida}"></label>
        <label class="campo"><span>Repita la cédula</span><input name="repetida" inputmode="numeric" autocomplete="off" required pattern="[0-9]{5,11}"></label>
        <label class="campo ancho"><span>Motivo</span><input name="motivo" maxlength="300" value="Corrección de un posible error de digitación"></label></form>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g">Corregir</button>` });
    $('#g', d).onclick = async () => {
      const f = $('#f-ced', d);
      if (!f.reportValidity()) return;
      const datos = datosForm(f);
      if (datos.cedula !== datos.repetida) { aviso('Las dos cédulas no coinciden', 'error'); return; }
      try { await resolver({ decision: 'corregir', cedula_correcta: datos.cedula, motivo: datos.motivo }); cerrar(); } catch (err) { avisoError(err); }
    };
  }

  async function solicitudes(c, mio) {
    const lista = await api.get('/api/solicitudes');
    if (!vigente(mio)) return;
    const plazo = (s) => {
      if (s.dias_restantes == null) return html`<span class="sec">Sin plazo legal</span>`;
      if (s.vencida) return html`<span class="chip rojo">Vencida (${fecha(s.vence)})</span>`;
      return html`<span class="chip ${s.dias_restantes <= 3 ? 'ambar' : 'verde'}">${num(s.dias_restantes)} días · ${fecha(s.vence)}</span>`;
    };
    const tabla = (filas, vacio) => (filas.length ? html`<div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Tipo</th><th>Persona</th><th>Descripción</th><th>Registró</th><th>Plazo</th><th>Estado</th><th></th></tr></thead>
      <tbody>${filas.map((s) => html`<tr style="cursor:default" data-s="${s.id}"><td><b>${TIPOS_SOLICITUD[s.tipo] || s.tipo}</b><div class="sec">${s.canal || ''}</div></td>
        <td>${s.persona_id ? html`<a href="/personas/${s.persona_id}" data-ruta>${s.persona || `Persona ${s.persona_id}`}</a>` : '—'}</td>
        <td style="max-width:340px;white-space:pre-wrap">${s.descripcion || ''}</td><td class="sec">${s.creado_por?.usuario || ''}<br>${fecha(s.ts, true)}</td>
        <td>${plazo(s)}</td><td>${ESTADOS_SOLICITUD[s.estado] || s.estado}</td>
        <td><button class="btn chico" data-responder="${s.id}">Responder</button></td></tr>`)}</tbody></table></div>` : html`<p class="sec">${vacio}</p>`);
    const titulares = lista.filter((s) => s.tipo !== 'registro');
    const registros = lista.filter((s) => s.tipo === 'registro');
    montar(c, html`<p class="sec">Consultas (10 días hábiles) y reclamos de corrección, supresión o revocatoria (15 días hábiles) de los titulares (Ley 1581, arts. 14 y 15). Mientras un reclamo está abierto, la persona sale de las colas.</p>
      ${tabla(titulares, 'No hay solicitudes abiertas de titulares.')}
      <h2 style="margin-top:22px">Pedidos de registro de consultores</h2>
      <p class="sec">Personas que llamaron y no están en la base: créelas usted desde Habitantes.</p>
      ${tabla(registros, 'No hay pedidos de registro abiertos.')}`);
    c.onclick = (e) => {
      const b = e.target.closest('[data-responder]');
      if (!b) return;
      const s = lista.find((x) => String(x.id) === b.dataset.responder);
      const { el: d, cerrar } = dialogo({ titulo: `${TIPOS_SOLICITUD[s.tipo] || s.tipo}${s.persona ? ` · ${s.persona}` : ''}`,
        cuerpo: html`<form class="form" id="f-sol"><p class="ancho" style="margin:0;white-space:pre-wrap">${s.descripcion || ''}</p>
          <label class="campo"><span>Estado</span><select name="estado">${Object.entries(ESTADOS_SOLICITUD).map(([k, t]) => html`<option value="${k}" ${k === s.estado ? 'selected' : ''}>${t}</option>`)}</select></label>
          <label class="campo ancho"><span>Respuesta al titular</span><textarea name="respuesta" maxlength="2000">${s.respuesta || ''}</textarea></label></form>`,
        pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g">Guardar</button>` });
      $('#g', d).onclick = async () => {
        try {
          await api.patch(`/api/solicitudes/${s.id}`, datosForm($('#f-sol', d)));
          cerrar(); aviso('Solicitud actualizada'); recargar(solicitudes, 'solicitudes', c);
        } catch (err) { avisoError(err); }
      };
    };
  }

  async function situaciones(c, mio) {
    const lista = await api.get('/api/situaciones');
    if (!vigente(mio)) return;
    if (!lista.length) { montar(c, html`<div class="tarjeta vacio"><b>Nada por confirmar</b>No hay personas reportadas como fallecidas o fuera de Yondó.</div>`); return; }
    montar(c, html`<p class="sec">Mientras no se revierta, la persona queda fuera de colas, listas de trabajo e indicadores. Nada se borra; si corresponde, suprímala desde su ficha.</p>
      <div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Persona</th><th>Situación</th><th>Lugar</th><th>Reportado</th><th></th></tr></thead>
      <tbody>${lista.map((p) => html`<tr style="cursor:default" data-p="${p.id}"><td><a href="/personas/${p.id}" data-ruta><b>${p.nombre}</b></a></td>
        <td><span class="chip ambar">${SITUACIONES[p.situacion?.estado] || p.situacion?.estado}</span></td><td>${titulo(p.lugar || '') || '—'}</td>
        <td class="sec">${fecha(p.situacion?.ts, true)}${p.situacion?.fuente ? ` · ${p.situacion.fuente}` : ''}</td>
        <td style="white-space:nowrap"><button class="btn chico primario" data-s="confirmar">Confirmar</button> <button class="btn chico" data-s="revertir">Revertir</button></td></tr>`)}</tbody></table></div>`);
    c.onclick = async (e) => {
      const b = e.target.closest('[data-s]');
      if (!b) return;
      b.disabled = true;
      try {
        await api.post(`/api/situaciones/${b.closest('[data-p]').dataset.p}`, { decision: b.dataset.s });
        aviso(b.dataset.s === 'confirmar' ? 'Situación confirmada' : 'La persona vuelve a estar activa');
        recargar(situaciones, 'situaciones', c);
      } catch (err) { avisoError(err); b.disabled = false; }
    };
  }

  async function lugares(c, mio) {
    const ls = await api.get('/api/lugares');
    if (!vigente(mio)) return;
    const sinPunto = ls.filter((l) => l.lat == null && l.n > 0);
    montar(c, html`
      ${sinPunto.length ? html`<div class="aviso-legal" style="margin-bottom:14px"><b>${num(sinPunto.length)} lugares con habitantes no tienen punto.</b> Ubíquelos en el mapa y todas sus personas quedarán georreferenciadas.</div>` : ''}
      <div style="display:flex;justify-content:flex-end;margin-bottom:10px"><button class="btn primario chico" id="nuevo-lugar">Nuevo lugar</button></div>
      <div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Lugar</th><th>Tipo</th><th>Zona</th><th class="num">Personas</th><th>Punto</th><th>Fuente</th><th></th></tr></thead>
      <tbody>${ls.map((l) => html`<tr style="cursor:default" data-l="${l.id}">
        <td><b>${titulo(l.nombre)}</b>${l.alias.length ? html`<div class="sec">También: ${l.alias.map(titulo).join(', ')}</div>` : ''}</td>
        <td>${l.tipo.replace('_', ' ')}</td><td>${l.zona}</td><td class="num">${num(l.n)}</td>
        <td>${l.lat != null ? html`<span class="chip verde">${l.tiene_poligono ? 'Polígono' : 'Punto'}</span>` : html`<span class="chip ambar">Falta</span>`}</td>
        <td class="sec">${l.fuente || ''}${l.precision ? ' · ' + l.precision : ''}</td>
        <td style="white-space:nowrap"><button class="btn chico" data-ubicar="${l.id}">Ubicar</button> <button class="btn chico fantasma" data-alias="${l.id}">Alias</button></td></tr>`)}</tbody></table></div>`);
    c.onclick = async (e) => {
      const u = e.target.closest('[data-ubicar]');
      if (u) {
        const l = ls.find((x) => x.id === Number(u.dataset.ubicar));
        const p = await elegirPunto({ titulo: `Ubicar ${titulo(l.nombre)}`, inicial: l.lat != null ? [l.lon, l.lat] : null,
          ayuda: 'Marque el centro del barrio o el caserío de la vereda. Las personas de este lugar sin dirección exacta tomarán este punto.' });
        if (!p) return;
        try {
          await api.patch(`/api/lugares/${l.id}`, { lon: p[0], lat: p[1] });
          aviso('Lugar ubicado y personas recalculadas'); recargar(lugares, 'lugares', c);
        } catch (err) { avisoError(err); }
        return;
      }
      const a = e.target.closest('[data-alias]');
      if (a) {
        const l = ls.find((x) => x.id === Number(a.dataset.alias));
        const { el: d, cerrar } = dialogo({ titulo: `Otros nombres de ${titulo(l.nombre)}`,
          cuerpo: html`<p class="sec" style="margin-top:0">Uno por línea: cómo lo escribe la gente en las direcciones.</p><textarea class="entrada" id="alias" style="min-height:140px">${l.alias.join('\n')}</textarea>`,
          pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g">Guardar</button>` });
        $('#g', d).onclick = async () => {
          try {
            await api.patch(`/api/lugares/${l.id}`, { alias: $('#alias', d).value.split('\n').map((s) => s.trim()).filter(Boolean) });
            cerrar(); aviso('Alias guardados; ubicaciones recalculadas'); recargar(lugares, 'lugares', c);
          } catch (err) { avisoError(err); }
        };
        return;
      }
      if (e.target.closest('#nuevo-lugar')) nuevoLugar('', () => recargar(lugares, 'lugares', c));
    };
  }

  async function sinReconocer(c, mio) {
    const [ls, todos] = await Promise.all([api.get('/api/lugares/sin-reconocer'), api.get('/api/lugares')]);
    if (!vigente(mio)) return;
    montar(c, html`<p class="sec">Nombres escritos en las direcciones que no coinciden con ningún barrio o vereda. Créelos como lugar nuevo o agréguelos como otro nombre de uno existente.</p>
      ${ls.length ? html`<div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Como lo escribieron</th><th class="num">Personas</th><th>Agregar como alias de…</th><th></th></tr></thead>
      <tbody>${ls.map((x) => html`<tr style="cursor:default" data-t="${x.texto}"><td><b>${x.texto}</b></td><td class="num">${num(x.n)}</td>
        <td><select class="entrada" data-destino><option value="">Elegir lugar…</option>${todos.map((l) => html`<option value="${l.id}">${titulo(l.nombre)} · ${l.tipo}</option>`)}</select></td>
        <td style="white-space:nowrap"><button class="btn chico" data-como-alias>Agregar</button> <button class="btn chico fantasma" data-crear>Crear lugar</button></td></tr>`)}</tbody></table></div>`
        : html`<div class="tarjeta vacio"><b>Todo reconocido</b></div>`}`);
    c.onclick = async (e) => {
      const tr = e.target.closest('tr[data-t]');
      if (!tr) return;
      const texto = tr.dataset.t;
      if (e.target.closest('[data-como-alias]')) {
        const dest = Number(tr.querySelector('[data-destino]').value);
        if (!dest) { aviso('Elija el lugar', 'error'); return; }
        const l = todos.find((x) => x.id === dest);
        try {
          await api.patch(`/api/lugares/${dest}`, { alias: [...l.alias, texto] });
          aviso(`«${texto}» ahora se reconoce como ${titulo(l.nombre)}`);
          recargar(sinReconocer, 'sin', c);
        } catch (err) { avisoError(err); }
      } else if (e.target.closest('[data-crear]')) nuevoLugar(texto, () => recargar(sinReconocer, 'sin', c));
    };
  }

  function nuevoLugar(nombre, despues) {
    let punto = null;
    const { el: d, cerrar } = dialogo({ titulo: 'Nuevo lugar',
      cuerpo: html`<form class="form" id="f-lugar">
        <label class="campo ancho"><span>Nombre</span><input name="nombre" value="${nombre}" required></label>
        <label class="campo"><span>Tipo</span><select name="tipo"><option value="barrio">Barrio</option><option value="sector">Sector</option><option value="vereda">Vereda</option>
          <option value="caserio">Caserío</option><option value="centro_poblado">Centro poblado</option><option value="corregimiento">Corregimiento</option></select></label>
        <label class="campo"><span>Zona</span><select name="zona"><option value="urbana">Urbana</option><option value="rural">Rural</option></select></label>
        <div class="ancho"><button type="button" class="btn chico" id="p">Marcar en el mapa</button> <span class="sec" id="pt"></span></div></form>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g">Crear</button>` });
    $('#p', d).onclick = async () => { punto = await elegirPunto({ titulo: 'Punto del lugar' }); if (punto) $('#pt', d).textContent = `${punto[1].toFixed(5)}, ${punto[0].toFixed(5)}`; };
    $('#g', d).onclick = async () => {
      const f = $('#f-lugar', d);
      if (!f.reportValidity()) return;
      const datos = datosForm(f);
      if (punto) { datos.lon = punto[0]; datos.lat = punto[1]; }
      try { await api.post('/api/lugares', datos); cerrar(); aviso('Lugar creado; personas recalculadas'); despues(); } catch (err) { aviso(err.message, 'error'); }
    };
  }

  el.addEventListener('click', async (e) => {
    const t = e.target.closest('[data-tab]');
    if (t) { pestana = t.dataset.tab; pintar(); }
    const regeo = e.target.closest('#regeo');
    if (regeo && !regeo.disabled) {
      regeo.disabled = true;
      try {
        const r = await api.post('/api/georreferenciar');
        aviso(`Ubicaciones recalculadas: ${num(Object.entries(r.por_precision).filter(([k]) => k !== 'sin_ubicar').reduce((a, [, v]) => a + v, 0))} ubicadas`);
      } catch (err) { avisoError(err); } finally { regeo.disabled = false; }
    }
  });
  pintar();
}
