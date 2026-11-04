// Ficha de un habitante: datos editables, necesidades, campos propios, ubicación, historial y origen de cada dato.
import { api, ErrorApi } from '../api.js';
import { refrescarInsignias } from '../app.js';
import { BASES, baseSegunTema, cargarMapLibre } from '../mapa3d.js';
import { $, $$, FUENTES, aviso, avisoError, chipPrecision, confirmar, crudo, datosForm, dialogo, fecha, html, iniciales, montar, num, titulo } from '../ui.js';
import { elegirPunto, opcionesLugares } from './comunes.js';

const NIVELES = ['Ninguno', 'Primaria', 'Secundaria', 'Técnico', 'Tecnólogo', 'Universitario', 'Posgrado'];

export async function vistaFicha(el, { params, ir }) {
  const id = Number(params[0]);
  let p, cat;
  try {
    [p, cat] = await Promise.all([api.get(`/api/personas/${id}`), api.get('/api/catalogos')]);
  } catch (e) {
    if (e instanceof ErrorApi && e.estado === 409 && e.detalle?.id) { ir(`/personas/${e.detalle.id}`, { reemplazar: true }); return; }
    throw e;
  }
  if (!el.isConnected) return; // mientras cargaba se pidió otra vista
  let pestana = 'datos';
  let mini = null, turnoMini = 0;
  let formInicial = null; // valores del formulario tal como se pintaron

  // Valores del formulario de datos (y chips de etiquetas) para no perder lo escrito al volver a pintar
  function leerForm() {
    const f = $('#f-datos', el);
    if (!f) return null;
    const v = {};
    for (const x of f.elements) if (x.name) v[x.name] = x.type === 'checkbox' ? x.checked : x.value;
    for (const b of $$('[data-et]', f)) v['et:' + b.dataset.et] = b.getAttribute('aria-pressed');
    return v;
  }

  function pintar({ conservar = true } = {}) {
    // Lo cambiado y no guardado sobrevive a las acciones que vuelven a pintar la ficha (nota, ubicación, unir)
    const ahora = conservar ? leerForm() : null;
    const pendientes = ahora && formInicial ? Object.entries(ahora).filter(([k, v]) => formInicial[k] !== v) : [];
    // `extra` son atributos escritos en este archivo: van sin escapar
    const campoTxt = (k, t, extra = '') => html`<label class="campo"><span>${t}</span><input name="${k}" value="${p[k] ?? ''}" ${crudo(extra)}></label>`;
    const sel = (k, t, ops) => html`<label class="campo"><span>${t}</span><select name="${k}">${ops.map(([v, tx]) => html`<option value="${v}" ${String(p[k] ?? '') === String(v) ? 'selected' : ''}>${tx}</option>`)}</select></label>`;
    const campos = cat.campos.filter((c) => c.activo);
    const grupos = { necesidad: 'Necesidades', interes: 'Grupo poblacional e intereses', rol: 'Rol en la comunidad' };
    const tiene = new Set(p.etiquetas.map((e) => e.id));
    const eventos = [
      ...p.reuniones.map((r) => ({ f: r.fecha, tipo: 'reunion', t: `Asistió a «${r.titulo}»`, m: [r.lugar_texto, r.rol, r.nota].filter(Boolean).join(' · '), href: `/reuniones/${r.id}` })),
      ...p.notas.map((n) => ({ f: n.creado_en, tipo: 'nota', t: n.texto, m: `${n.autor || ''}${n.reunion ? ' · en ' + n.reunion : ''}`, nota: n.id })),
      ...p.tramites.map((t) => ({ f: t.fecha, tipo: 'tramite', t: titulo(t.tipo || 'Trámite'), m: [t.ficha && 'Ficha ' + t.ficha, t.direccion].filter(Boolean).join(' · ') })),
    ].sort((a, b) => String(b.f || '').localeCompare(String(a.f || '')));

    montar(el, html`
      <div class="miga"><a href="/personas" data-ruta>Habitantes</a> › Ficha ${p.id}</div>
      <div class="cabecera">
        <div class="perfil">
          <div class="avatar">${iniciales(p.nombre)}</div>
          <div><h1 style="font-size:32px">${p.nombre}</h1>
            <div class="chips" style="margin-top:8px">
              ${p.cedula ? html`<span class="chip">CC ${p.cedula}</span>` : html`<span class="chip ambar">Sin cédula</span>`}
              ${p.fuentes.map((f) => html`<span class="chip borde">${FUENTES[f] || f}</span>`)}
              ${p.lider ? html`<span class="chip rojo">Líder</span>` : ''}
              <span class="chip ${p.consentimiento === 'si' ? 'verde' : p.consentimiento === 'no' ? 'rojo' : 'ambar'}">Autorización: ${p.consentimiento}</span>
              ${p.listas.map((l) => html`<span class="chip azul">${l}</span>`)}
            </div></div>
        </div>
        <div class="acciones" style="align-items:center">
          <div class="anillo" style="--p:${p.completitud}" title="Completitud del perfil"><span>${p.completitud}%</span></div>
          <button class="btn" id="unir">Unir con otra ficha</button>
          <button class="btn peligro" id="suprimir">Suprimir datos</button>
        </div>
      </div>
      ${p.coincidencias.length ? html`<div class="aviso-legal" style="margin-bottom:16px">Posible misma persona que ${p.coincidencias.map((c) => html`<a href="/personas/${c.otro_id}" data-ruta>${c.otro_nombre}</a> (${Math.round(c.puntaje * 100)} %) `)} — <a href="/calidad" data-ruta>revisar</a></div>` : ''}
      <div class="ficha">
        <div class="tarjeta">
          <div class="pestanas" role="tablist">
            ${[['datos', 'Datos y necesidades'], ['historial', `Historial (${eventos.length})`], ['origen', 'Origen de los datos'], ['cambios', 'Cambios']].map(([k, t]) => html`<button role="tab" data-tab="${k}" aria-selected="${pestana === k}">${t}</button>`)}
          </div>
          <div data-panel="datos" ${pestana === 'datos' ? '' : 'hidden'}>
            <form id="f-datos">
              <div class="form">
                ${campoTxt('nombre', 'Nombre completo', 'required')}
                ${campoTxt('cedula', 'Cédula', 'inputmode="numeric"')}
                ${sel('sexo', 'Sexo', [['', '—'], ['F', 'Mujer'], ['M', 'Hombre']])}
                ${campoTxt('edad', 'Edad', 'type="number" min="0" max="120"')}
                ${campoTxt('fecha_nacimiento', 'Fecha de nacimiento', 'type="date"')}
                ${campoTxt('telefono', 'Celular', 'inputmode="tel"')}
                ${campoTxt('telefono2', 'Otro teléfono', 'inputmode="tel"')}
                ${campoTxt('correo', 'Correo', 'type="email"')}
                <label class="campo ancho"><span>Dirección</span><input name="direccion" value="${p.direccion ?? ''}"></label>
                <label class="campo"><span>Barrio / vereda</span><select name="lugar_id">${opcionesLugares(cat, p.lugar_id)}</select></label>
                ${campoTxt('ocupacion', 'Ocupación')}
                ${sel('nivel_educativo', 'Nivel educativo', [['', '—'], ...NIVELES.map((n) => [n, n])])}
                ${campoTxt('personas_hogar', 'Personas en el hogar', 'type="number" min="0" max="40"')}
                ${campoTxt('puesto_votacion', 'Puesto de votación')}
                ${campoTxt('mesa', 'Mesa')}
                ${sel('consentimiento', 'Autorización de tratamiento de datos', [['pendiente', 'Pendiente'], ['si', 'Sí, autorizó'], ['no', 'No autorizó']])}
                ${campoTxt('consentimiento_fecha', 'Fecha de la autorización', 'type="date"')}
                <label class="interruptor" style="align-self:end"><span>Líder comunitario</span><input type="checkbox" name="lider" ${p.lider ? 'checked' : ''}></label>
                ${campos.map((c) => {
                  const v = p.extra[c.clave] ?? '';
                  const nombre = `extra.${c.clave}`;
                  if (c.tipo === 'opcion') return html`<label class="campo"><span>${c.etiqueta}</span><select name="${nombre}"><option value="">—</option>${c.opciones.map((o) => html`<option ${o === v ? 'selected' : ''}>${o}</option>`)}</select></label>`;
                  if (c.tipo === 'si_no') return html`<label class="campo"><span>${c.etiqueta}</span><select name="${nombre}"><option value="">—</option><option ${v === 'Sí' ? 'selected' : ''}>Sí</option><option ${v === 'No' ? 'selected' : ''}>No</option></select></label>`;
                  // step="any": los números propios pueden tener decimales (hectáreas, metros)
                  if (c.tipo === 'numero') return html`<label class="campo"><span>${c.etiqueta}</span><input name="${nombre}" value="${v}" type="number" step="any" inputmode="decimal"></label>`;
                  return html`<label class="campo"><span>${c.etiqueta}</span><input name="${nombre}" value="${v}" type="${c.tipo === 'fecha' ? 'date' : 'text'}"></label>`;
                })}
                <label class="campo ancho"><span>Observaciones</span><textarea name="observaciones">${p.observaciones ?? ''}</textarea></label>
              </div>
              ${Object.entries(grupos).map(([g, t]) => html`<div class="campo" style="margin-top:16px"><span>${t}</span><div class="chips">
                ${cat.etiquetas.filter((e) => e.grupo === g).map((e) => html`<button type="button" class="chip" data-et="${e.id}" aria-pressed="${tiene.has(e.id)}">${e.nombre}</button>`)}</div></div>`)}
              <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:18px;position:sticky;bottom:0;background:var(--surface);padding:10px 0">
                <span class="sec" id="estado-form" style="margin-right:auto;align-self:center"></span>
                <button class="btn primario" type="submit">Guardar cambios</button>
              </div>
            </form>
          </div>
          <div data-panel="historial" ${pestana === 'historial' ? '' : 'hidden'}>
            <form id="f-nota" style="display:flex;gap:8px;margin-bottom:18px"><input class="entrada" name="texto" placeholder="Agregar una nota o lo que se habló con esta persona…" required maxlength="4000"><button class="btn oscuro">Anotar</button></form>
            ${eventos.length ? html`<div class="linea-tiempo">${eventos.map((e) => html`<div class="ev"><span class="punto ${e.tipo}"></span><div>
              <div class="t">${e.href ? html`<a href="${e.href}" data-ruta>${e.t}</a>` : e.t}</div>
              <div class="m">${fecha(e.f, e.tipo === 'nota')}${e.m ? ' · ' + e.m : ''} ${e.nota ? html`<button class="btn fantasma chico" data-borrar-nota="${e.nota}">Borrar</button>` : ''}</div></div></div>`)}</div>`
              : html`<div class="vacio"><b>Sin historial</b>Registre su asistencia a una reunión o agregue una nota.</div>`}
          </div>
          <div data-panel="origen" ${pestana === 'origen' ? '' : 'hidden'}>
            ${p.origen.length ? p.origen.map((o) => html`<h3 style="font-size:14px;margin:6px 0 10px">${FUENTES[o.fuente] || o.fuente}</h3><div class="datos">
              ${Object.entries(o.datos).filter(([k]) => !['extra'].includes(k)).map(([k, v]) => html`<div><span>${k.replace(/_/g, ' ')}</span><b>${Array.isArray(v) ? v.join(', ') : v}</b></div>`)}</div>`) : ''}
            <h3 style="font-size:14px;margin:20px 0 10px">Trámites (${p.tramites.length})</h3>
            ${p.tramites.length ? html`<div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Fecha</th><th>Trámite</th><th>Ficha</th><th>Dirección</th><th>Teléfono</th></tr></thead>
              <tbody>${p.tramites.map((t) => html`<tr style="cursor:default"><td>${fecha(t.fecha)}</td><td>${titulo(t.tipo || '')}</td><td class="sec">${t.ficha}</td><td>${t.direccion}</td><td>${(t.telefono || '').replace(/;/g, ', ')}</td></tr>`)}</tbody></table></div>`
              : html`<p class="sec">No aparece en la base de trámites.</p>`}
          </div>
          <div data-panel="cambios" ${pestana === 'cambios' ? '' : 'hidden'}>
            ${p.historial.length ? html`<div class="linea-tiempo">${p.historial.map((h) => html`<div class="ev"><span class="punto"></span><div>
              <div class="t">${h.usuario || 'sistema'} · ${h.accion.replace(/_/g, ' ')}</div><div class="m">${fecha(h.ts, true)}</div>
              ${h.detalle ? html`<pre style="white-space:pre-wrap;font:12px/1.4 var(--f-mono);color:var(--muted);margin:4px 0 0">${resumenDetalle(h.detalle)}</pre>` : ''}</div></div>`)}</div>`
              : html`<p class="sec">Sin cambios registrados.</p>`}
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:16px">
          <section class="tarjeta">
            <header><h2>Ubicación</h2>${chipPrecision(p.geo_precision)}</header>
            <div class="minimapa" id="minimapa">${p.lat == null ? html`<div class="vacio" style="padding-top:80px">Sin coordenada</div>` : ''}</div>
            <div class="datos" style="margin-top:12px;grid-template-columns:1fr">
              <div><span>Dirección normalizada</span><b>${p.direccion_norm || '—'}</b></div>
              <div><span>Escrita originalmente</span><b>${p.direccion || '—'}</b></div>
              <div><span>Lugar</span><b>${p.lugar_nombre ? titulo(p.lugar_nombre) + ' · ' + (p.lugar_tipo || '').replace('_', ' ') : (p.lugar_texto ? titulo(p.lugar_texto) + ' (no reconocido)' : '—')}</b></div>
            </div>
            <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
              <button class="btn chico" id="ubicar">Ajustar en el mapa</button>
              ${p.geo_manual ? html`<button class="btn chico fantasma" id="automatica">Volver a la automática</button>` : ''}
            </div>
          </section>
          <section class="tarjeta">
            <h2>Contacto</h2>
            <div class="datos" style="grid-template-columns:1fr">
              <div><span>Celular</span><b>${p.telefono || '—'}${p.telefono2 ? ' · ' + p.telefono2 : ''}</b></div>
              <div><span>Correo</span><b>${p.correo || '—'}</b></div>
              <div><span>Último contacto</span><b>${fecha(p.ultimo_contacto)}</b></div>
              <div><span>Reuniones</span><b>${num(p.reuniones.length)}</b></div>
            </div>
            ${p.telefono ? html`<div style="display:flex;gap:8px;margin-top:12px"><a class="btn chico" href="tel:${p.telefono}">Llamar</a>
              <a class="btn chico" href="https://wa.me/57${p.telefono}" target="_blank" rel="noopener noreferrer">WhatsApp</a></div>` : ''}
          </section>
        </div>
      </div>`);
    formInicial = leerForm();
    if (pendientes.length) {
      const f = $('#f-datos', el);
      for (const [k, v] of pendientes) {
        if (k.startsWith('et:')) { $(`[data-et="${k.slice(3)}"]`, f)?.setAttribute('aria-pressed', v); continue; }
        const x = f.elements.namedItem(k);
        if (x) x[x.type === 'checkbox' ? 'checked' : 'value'] = v;
      }
      $('#estado-form', el).textContent = 'Cambios sin guardar';
    }
    pintarMini();
  }

  async function pintarMini() {
    const turno = ++turnoMini;
    if (mini) { mini.remove(); mini = null; }
    if (p.lat == null) return;
    const maplibregl = await cargarMapLibre();
    // Mientras cargaba el motor de mapas se volvió a pintar la ficha o se salió de ella: ese mapa ya no va
    if (turno !== turnoMini || !el.isConnected) return;
    const cont = $('#minimapa', el);
    if (!cont) return;
    mini = new maplibregl.Map({ container: cont, style: BASES[baseSegunTema()], center: [p.lon, p.lat],
      zoom: p.geo_precision === 'vereda' ? 13 : 16.2, pitch: 45, attributionControl: { compact: true }, interactive: true });
    new maplibregl.Marker({ color: '#e3141b' }).setLngLat([p.lon, p.lat]).addTo(mini);
  }

  el.addEventListener('click', async (e) => {
    const tab = e.target.closest('[data-tab]');
    if (tab) {
      // Cambiar de pestaña no vuelve a pintar: lo escrito y no guardado sigue en el formulario
      pestana = tab.dataset.tab;
      for (const b of $$('[data-tab]', el)) b.setAttribute('aria-selected', b === tab);
      for (const panel of $$('[data-panel]', el)) panel.hidden = panel.dataset.panel !== pestana;
      return;
    }
    const et = e.target.closest('[data-et]');
    if (et) { et.setAttribute('aria-pressed', et.getAttribute('aria-pressed') !== 'true'); $('#estado-form', el).textContent = 'Cambios sin guardar'; return; }
    const bn = e.target.closest('[data-borrar-nota]');
    if (bn && await confirmar('¿Borrar esta nota?', { si: 'Borrar', peligro: true })) {
      try { p = await api.del(`/api/personas/${id}/notas/${bn.dataset.borrarNota}`); pintar(); } catch (err) { avisoError(err); }
      return;
    }
    if (e.target.closest('#ubicar')) {
      const punto = await elegirPunto({ inicial: p.lat != null ? [p.lon, p.lat] : null, titulo: `Ubicar a ${titulo(p.nombre)}` });
      if (!punto) return;
      try { p = await api.put(`/api/personas/${id}/ubicacion`, { lon: punto[0], lat: punto[1] }); aviso('Ubicación guardada'); pintar(); } catch (err) { avisoError(err); }
      return;
    }
    if (e.target.closest('#automatica')) {
      try { p = await api.del(`/api/personas/${id}/ubicacion`); pintar(); } catch (err) { avisoError(err); }
      return;
    }
    if (e.target.closest('#suprimir')) {
      if (await confirmar(`Se borrarán todos los datos personales de ${p.nombre} (derecho de supresión, Ley 1581). Queda solo el registro de auditoría. ¿Continuar?`, { si: 'Suprimir', peligro: true })) {
        await api.del(`/api/personas/${id}`); aviso('Datos suprimidos'); ir('/personas');
      }
      return;
    }
    if (e.target.closest('#unir')) unir();
  });
  el.addEventListener('input', (e) => { if (e.target.closest('#f-datos')) $('#estado-form', el).textContent = 'Cambios sin guardar'; });
  el.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (e.target.id === 'f-nota') {
      try {
        p = await api.post(`/api/personas/${id}/notas`, { texto: e.target.texto.value });
        aviso('Nota guardada'); pintar();
      } catch (err) { avisoError(err); }
      return;
    }
    if (e.target.id !== 'f-datos') return;
    const d = datosForm(e.target);
    const cuerpo = { extra: {} };
    for (const [k, v] of Object.entries(d)) {
      if (k.startsWith('extra.')) { cuerpo.extra[k.slice(6)] = v; continue; }
      const antes = k === 'lugar_id' ? p.lugar_id : p[k];
      const val = k === 'lugar_id' ? (v ? Number(v) : null) : k === 'lider' ? v : v;
      if (String(antes ?? '') !== String(val ?? '') && !(k === 'lider' && !!antes === !!val)) cuerpo[k] = val === '' ? null : val;
    }
    cuerpo.etiquetas = $$('[data-et][aria-pressed="true"]', el).map((b) => Number(b.dataset.et));
    try {
      p = await api.patch(`/api/personas/${id}`, cuerpo);
      aviso('Ficha actualizada');
      pintar({ conservar: false });
    } catch (err) {
      if (err instanceof ErrorApi && err.detalle?.id) aviso(`${err.message} (ficha ${err.detalle.id})`, 'error', 6000);
      else aviso(err.message, 'error', 6000);
    }
  });

  async function unir() {
    const { el: d, cerrar } = dialogo({
      titulo: 'Unir con otra ficha', ancho: true,
      cuerpo: html`<p class="sec" style="margin-top:0">Busque la otra ficha de esta misma persona. Esta ficha conserva sus datos y recibe lo que le falte, más los trámites, reuniones y notas de la otra.</p>
        <input class="entrada" id="buscar-unir" placeholder="Nombre, cédula o teléfono">
        <div class="resultados" id="res-unir"></div>`,
    });
    const pintarRes = (lista) => montar($('#res-unir', d), html`${lista.filter((x) => x.id !== id).map((x) => html`<div class="resultado"><div class="q"><b>${x.nombre}</b>
      <small>${x.cedula || 'sin cédula'} · ${x.telefono || 'sin teléfono'} · ${titulo(x.lugar || '')}${x.parecido ? ` · parecido ${x.parecido} %` : ''}</small></div>
      <button class="btn chico oscuro" data-con="${x.id}">Unir</button></div>`)}`);
    pintarRes(await api.get(`/api/personas/${id}/parecidas`));
    $('#buscar-unir', d).addEventListener('input', async (ev) => { if (ev.target.value.length >= 2) pintarRes(await api.get('/api/buscar', { q: ev.target.value })); });
    $('#res-unir', d).addEventListener('click', async (ev) => {
      const b = ev.target.closest('[data-con]');
      if (!b) return;
      try {
        p = await api.post(`/api/personas/${id}/fusionar`, { con_id: Number(b.dataset.con) });
        cerrar(); aviso('Fichas unidas'); pintar(); refrescarInsignias();
      } catch (err) { aviso(err.message, 'error'); }
    });
  }

  pintar();
  return () => { turnoMini++; mini?.remove(); mini = null; };
}

function resumenDetalle(txt) {
  try {
    const d = JSON.parse(txt);
    return Object.entries(d).map(([k, v]) => `${k}: ${v && typeof v === 'object' && 'antes' in v ? `${v.antes ?? '—'} → ${v.despues ?? '—'}` : JSON.stringify(v)}`).join('\n');
  } catch { return txt; }
}

