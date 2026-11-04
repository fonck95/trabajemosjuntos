// Calidad de datos: confirmar coincidencias por nombre, ubicar lugares sin punto y reconocer nombres nuevos.
import { api } from '../api.js';
import { refrescarInsignias } from '../app.js';
import { $, aviso, avisoError, datosForm, dialogo, html, montar, num, titulo } from '../ui.js';
import { elegirPunto } from './comunes.js';

export async function vistaCalidad(el, { q }) {
  let pestana = q.get('p') || 'coincidencias';
  montar(el, html`
    <div class="cabecera"><div><h1>Calidad de datos</h1><div class="sub">Lo que la máquina no decide sola: usted confirma, y la base queda más completa.</div></div>
      <div class="acciones"><button class="btn" id="regeo">Recalcular ubicaciones</button></div></div>
    <div class="pestanas" role="tablist">
      ${[['coincidencias', 'Coincidencias por revisar'], ['lugares', 'Barrios y veredas'], ['sin', 'Lugares sin reconocer']].map(([k, t]) => html`<button role="tab" data-tab="${k}" aria-selected="${k === pestana}">${t}</button>`)}
    </div>
    <div id="cuerpo"></div>`);

  // Cada carga lleva un turno: si se cambió de pestaña mientras llegaba, no pinta encima de la nueva
  let turno = 0;
  const vigente = (t) => t === turno && el.isConnected;

  async function pintar() {
    for (const b of el.querySelectorAll('[data-tab]')) b.setAttribute('aria-selected', b.dataset.tab === pestana);
    history.replaceState({}, '', `/calidad?p=${pestana}`);
    const c = $('#cuerpo', el);
    montar(c, html`<div class="cargando"><div class="giro"></div></div>`);
    c.onclick = null;
    const t = ++turno;
    if (pestana === 'coincidencias') return coincidencias(c, t);
    if (pestana === 'lugares') return lugares(c, t);
    return sinReconocer(c, t);
  }
  // Vuelve a cargar la pestaña después de una acción, solo si el usuario sigue en ella
  const recargar = (fn, nombre, c) => { if (pestana === nombre && el.isConnected) fn(c, ++turno); };

  async function coincidencias(c, mio) {
    const lista = await api.get('/api/coincidencias');
    if (!vigente(mio)) return;
    if (!lista.length) { montar(c, html`<div class="tarjeta vacio"><b>Nada pendiente</b>Todas las coincidencias por nombre están resueltas.</div>`); return; }
    const marcar = (a, b) => {
      const tb = new Set((b || '').split(/\s+/));
      return html`${(a || '').split(/\s+/).map((w) => (tb.has(w) ? html`<span class="igual">${w}</span> ` : html`${w} `))}`;
    };
    const lado = (p, otro, rotulo) => html`<div class="lado"><span class="sec">${rotulo}</span><b><a href="/personas/${p.id}" data-ruta>${marcar(p.nombre, otro.nombre)}</a></b>
      <dl><dt>Cédula</dt><dd>${p.cedula || '—'}</dd><dt>Teléfono</dt><dd>${[p.telefono, p.telefono2].filter(Boolean).join(', ') || '—'}</dd>
      <dt>Lugar</dt><dd>${titulo(p.lugar || '') || '—'}</dd><dt>Dirección</dt><dd>${p.direccion || '—'}</dd>
      ${p.edad ? html`<dt>Edad</dt><dd>${p.edad} · ${p.sexo || ''}</dd>` : ''}${p.tramites ? html`<dt>Trámites</dt><dd>${p.tramites}</dd>` : ''}
      ${p.listas ? html`<dt>Listas</dt><dd>${p.listas}</dd>` : ''}</dl></div>`;
    // Pares y, como en el panel y la insignia, personas con cédula por revisar (`ids`: una por par)
    const cuenta = (ids) => {
      const personas = new Set(ids).size;
      return `${num(ids.length)} ${ids.length === 1 ? 'par' : 'pares'} de fichas con nombres parecidos (${num(personas)} ${personas === 1 ? 'persona' : 'personas'} por revisar).`;
    };
    montar(c, html`<p class="sec"><span id="cuenta-pares">${cuenta(lista.map((x) => x.persona.id))}</span> Si son la misma persona, se unen: la ficha de trámites recibe la cédula y las listas.</p>
      <div style="display:flex;flex-direction:column;gap:12px">${lista.map((x) => html`<div class="tarjeta" data-c="${x.id}" data-p="${x.persona.id}"><div class="par">
        ${lado(x.persona, x.candidato, x.detalle.homonimo ? 'Mismo nombre, otra ficha' : 'Base con cédula')}
        <div class="medio"><span class="puntaje">${Math.round(x.puntaje * 100)}%</span>
          <span class="sec" style="text-align:center">${x.detalle.palabras} palabras${x.detalle.telefono ? html`<br><span class="chip verde">mismo teléfono</span>` : ''}${x.detalle.correo ? html`<br><span class="chip verde">mismo correo</span>` : ''}</span>
          <button class="btn chico primario" data-d="aceptar">Es la misma</button><button class="btn chico" data-d="rechazar">Son distintas</button></div>
        ${lado(x.candidato, x.persona, x.detalle.homonimo ? 'Mismo nombre, otra ficha' : 'Base de trámites')}</div></div>`)}</div>`);
    c.onclick = async (e) => {
      const b = e.target.closest('[data-d]');
      if (!b) return;
      const t = b.closest('[data-c]');
      b.disabled = true;
      try {
        await api.post(`/api/coincidencias/${t.dataset.c}`, { decision: b.dataset.d });
        aviso(b.dataset.d === 'aceptar' ? 'Fichas unidas' : 'Marcadas como personas distintas');
        refrescarInsignias();
        // Unir borra en el servidor las demás coincidencias de esa ficha: se vuelve a pedir la lista
        if (b.dataset.d === 'aceptar') { recargar(coincidencias, 'coincidencias', c); return; }
        t.style.transition = 'opacity .25s'; t.style.opacity = 0;
        setTimeout(() => {
          t.remove();
          const rotulo = $('#cuenta-pares', c);
          if (rotulo) rotulo.textContent = cuenta([...c.querySelectorAll('[data-c]')].map((x) => x.dataset.p));
        }, 260);
      } catch (err) {
        aviso(err.message, 'error'); b.disabled = false;
        if (err.estado === 404) recargar(coincidencias, 'coincidencias', c); // ya resuelta: la tarjeta sobra
      }
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
