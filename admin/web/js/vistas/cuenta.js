// Mi cuenta (7.9): cambio de clave, compromiso de confidencialidad e indicadores propios. Con la clave temporal o el
// compromiso pendientes, es la única vista que se abre. El coordinador cambia su clave y acepta el compromiso como
// planilleros y consultores; solo el administrador de `.env` (uid 0) no tiene clave en el panel.
// «Agentes por MCP» (app/api/mcp.py y app/api/pantalla.py): dos claves, cada una de un tipo. La de la presentación
// maneja la pantalla en off de la propuesta y nada más. La de datos (solo A y K, según Ajustes) deja a un agente externo
// leer personas (solo A), ver la analítica o proponer cambios; esos datos salen del panel hacia ese cliente, y cada
// cambio propuesto espera aquí, entero, a que la persona lo apruebe o lo rechace (uno por uno). Cada clave se muestra
// una sola vez, al crearla; cambiar la clave del panel las anula. `/cuenta?propuesta=<id>` resalta esa propuesta.
import { api, configurar, nombreRol, puede, sesion } from '../api.js';
import { refrescarInsignias } from '../app.js';
import { url } from '../base.js';
import { $, aviso, avisoError, confirmar, fecha, html, montar } from '../ui.js';
import { pintarIndicadores } from './usuarios.js';

// Los alcances de una clave de datos, en el orden del servidor (`pantalla.ALCANCES_DATOS`)
const ALCANCES = [
  ['lectura', 'Leer personas', 'Buscar, ver fichas, reuniones y pendientes, con cédula y teléfono enmascarados, sin datos sensibles ni de quien no autorizó.'],
  ['analitica', 'Analítica', 'Cifras agregadas del panel (análisis y diagnóstico), sin personas y con las celdas pequeñas ocultas.'],
  ['escritura', 'Proponer cambios', 'El agente propone y nada se guarda hasta que usted lo aprueba aquí, uno por uno.'],
];
const NOMBRE_ALCANCE = Object.fromEntries(ALCANCES.map(([k, t]) => [k, t]));
const ESTADOS = { hecha: 'Hecha', rechazada: 'Rechazada', fallida: 'No se pudo', anulada: 'Anulada', en_curso: 'Guardándose…' };

export async function vistaCuenta(el, { ir, q } = {}) {
  const yo = await api.get('/api/yo');
  const admin = yo.rol === 'admin' && !yo.uid; // el administrador de `.env`
  // Si entró con algo pendiente, al ponerse al día vuelve a su inicio
  const pendienteAlEntrar = yo.debe_cambiar_clave || yo.compromiso_pendiente;
  // La propuesta del enlace que dio el agente (`aprobar_en`): se resalta una sola vez
  let propuestaPedida = q?.get?.('propuesta') || null;

  function pintar() {
    const pendiente = yo.debe_cambiar_clave ? 'clave' : yo.compromiso_pendiente ? 'compromiso' : null;
    montar(el, html`
      <div class="cabecera"><div><h1>Mi cuenta</h1><div class="sub">${yo.nombre || yo.usuario} · ${nombreRol(yo.rol)}</div></div></div>
      ${pendiente === 'clave' ? html`<div class="aviso-cuenta" role="alert"><b>Cambie su clave temporal para continuar.</b> La clave que le dio el administrador sirve una sola vez.</div>` : ''}
      ${pendiente === 'compromiso' ? html`<div class="aviso-cuenta" role="alert"><b>Lea y acepte el compromiso de confidencialidad para continuar.</b></div>` : ''}
      <div class="rejilla r-12">
        <section class="tarjeta c-6" id="t-clave">
          <h2>Clave</h2>
          ${admin ? html`<p class="sec">La clave del administrador se cambia en Railway (variable <b>password</b>). Al cambiarla se cierran todas las sesiones.</p>` : html`
          <form id="f-clave" class="form-cuenta" novalidate>
            <label class="campo"><span>${yo.debe_cambiar_clave ? 'Clave temporal' : 'Clave actual'}</span><input name="actual" type="password" autocomplete="current-password" required></label>
            <label class="campo"><span>Clave nueva</span><input name="nueva" type="password" autocomplete="new-password" minlength="10" required></label>
            <label class="campo"><span>Repita la clave nueva</span><input name="repetida" type="password" autocomplete="new-password" minlength="10" required></label>
            <p class="sec">Al menos 10 caracteres, distinta de su usuario y difícil de adivinar. Una frase de tres o cuatro palabras sirve.</p>
            <div class="error" role="alert"></div>
            <div><button class="btn primario" type="submit">Cambiar clave</button></div>
          </form>`}
        </section>
        <section class="tarjeta c-6" id="t-compromiso">
          <h2>Compromiso de confidencialidad</h2>
          ${admin ? html`<p class="sec">El administrador responde por la base ante el titular. Los coordinadores, planilleros y consultores aceptan este compromiso antes de trabajar.</p>` : html`
          <ol class="compromiso">${(yo.compromiso?.puntos || []).map((p) => html`<li>${p}</li>`)}</ol>
          <p class="sec">Versión ${yo.compromiso?.version || '—'}${yo.compromiso?.aceptado ? html` · aceptado el ${fecha(yo.compromiso.aceptado_en, true)}` : ''}</p>
          ${yo.compromiso?.aceptado ? '' : html`<button class="btn primario" id="aceptar" ${yo.debe_cambiar_clave ? 'disabled title="Primero cambie su clave temporal"' : ''}>Acepto el compromiso</button>`}`}
        </section>
        ${!pendiente && puede('presentacion.ver') ? html`<section class="tarjeta c-12" id="t-mcp">
          <header><h2>Agentes por MCP</h2><span class="nota">Claude, Mnemo u otro cliente MCP</span></header>
          <p class="sec">Un agente externo trabaja con una clave suya. La de la presentación maneja su <a href="${url('/presentacion?off=1')}" target="_blank" rel="noopener">pantalla en off</a>: ir a un capítulo y paso, poner una frase en pantalla, cambiar lo que se ve y hacer que llene la ventana (la misma herramienta del asistente del panel). Con ella no se ve ni se cambia ningún dato de personas.</p>
          <div id="mcp"><div class="cargando"><div class="giro"></div></div></div>
        </section>` : ''}
        <section class="tarjeta c-12" id="t-indicadores">
          <header><h2>Mis indicadores</h2><span class="nota">Últimos 30 días</span></header>
          <div id="indicadores">${pendiente ? html`<p class="sec">Aparecen cuando su cuenta esté al día.</p>` : html`<div class="cargando"><div class="giro"></div></div>`}</div>
        </section>
      </div>`);
    if (!pendiente) cargarIndicadores();
    if ($('#mcp', el)) cargarMcp();
    if (pendiente === 'clave') el.querySelector('#f-clave [name=actual]')?.focus();
  }

  async function cargarIndicadores() {
    const c = $('#indicadores', el);
    try {
      const ind = await api.get('/api/yo/indicadores');
      if (c.isConnected) pintarIndicadores(c, ind, { rol: yo.rol });
    } catch (e) {
      if (c.isConnected) montar(c, html`<p class="sec">${e.message}</p>`);
    }
  }

  // ¿Esta persona ve el bloque de datos? Si puede pedir algún alcance, si ya tiene una clave de datos o si le quedan
  // propuestas por decidir (una clave que ya no vale deja las suyas anuladas, pero se ven en «Últimas decididas»)
  const conDatos = (info) => (info.permitidos || []).length > 0 || info.datos?.tiene || info.propuestas_pendientes > 0;

  function pintarDatos(info, nueva) {
    const d = info.datos || {};
    const motivos = info.motivos || {};
    const elegidos = new Set(d.tiene ? d.alcances : []);
    const suspendidos = (d.alcances || []).filter((a) => !(d.vigentes || []).includes(a));
    return html`<div class="mcp-datos" id="mcp-datos">
      <h3>Datos del panel</h3>
      <div class="aviso-legal mcp-aviso" role="note">
        <p><b>Los datos que pida el agente salen del panel</b> hacia ese cliente (Claude, ChatGPT u otro): es un tercero que usted elige, y usted responde por esos datos ante su titular (Ley 1581 de 2012 y su compromiso de confidencialidad). Úsela solo para la tarea y revóquela al terminar.</p>
        <p>Va solo en la cabecera <code>Authorization: Bearer …</code>, vence a los 30 días y nunca maneja la pantalla en off. Cada cambio que proponga el agente espera aquí su aprobación.</p>
      </div>
      <dl class="datos-mcp">
        <dt>Clave de datos</dt><dd>${d.tiene ? html`Creada el ${fecha(d.creada, true)} · vence el ${fecha(d.expira, true)}${d.usada ? html` · usada por última vez el ${fecha(d.usada, true)}` : ' · todavía sin usar'}` : 'Sin clave de datos'}</dd>
        ${d.tiene ? html`<dt>Permisos</dt><dd>${d.alcances.map((a) => NOMBRE_ALCANCE[a] || a).join(', ') || '—'}${suspendidos.length ? html` <span class="sec">(hoy no valen: ${suspendidos.map((a) => NOMBRE_ALCANCE[a] || a).join(', ')})</span>` : ''}</dd>` : ''}
      </dl>
      <fieldset class="mcp-alcances">
        <legend>Permisos de la clave</legend>
        ${ALCANCES.map(([k, t, texto]) => {
          const motivo = motivos[k];
          return html`<label class="mcp-alcance${motivo ? ' no' : ''}"><input type="checkbox" name="alcance" value="${k}" ${elegidos.has(k) && !motivo ? 'checked' : ''} ${motivo ? 'disabled' : ''}>
            <span><b>${t}</b><span class="sec">${motivo || texto}</span></span></label>`;
        })}
      </fieldset>
      ${nueva ? html`<div class="aviso-legal mcp-nueva" role="status">
        <p><b>Copie la clave ahora: no se vuelve a mostrar.</b> Va solo en la cabecera <code>Authorization: Bearer …</code> del cliente MCP: en una dirección quedaría en los registros y el panel la rechaza.</p>
        <div class="mcp-copiar"><label class="campo"><span>Clave de datos</span><input id="mcp-clave-datos" readonly value="${nueva.clave}"></label><button type="button" class="btn" data-copiar="mcp-clave-datos">Copiar</button></div>
      </div>` : ''}
      <div class="fila-botones">
        ${(info.permitidos || []).length ? html`<button type="button" class="btn ${d.tiene ? '' : 'primario'}" id="mcp-crear-datos">${d.tiene ? 'Crear otra clave de datos' : 'Crear clave de datos'}</button>` : ''}
        ${d.tiene ? html`<button type="button" class="btn" id="mcp-revocar-datos">Revocar la clave de datos</button>` : ''}
      </div>
      <div id="mcp-propuestas"></div>
    </div>`;
  }

  function pintarMcp(info, nueva = null) {
    const c = $('#mcp', el);
    if (!c?.isConnected) return;
    const presentacion = nueva && nueva.tipo !== 'datos' ? nueva : null;
    const datos = nueva && nueva.tipo === 'datos' ? nueva : null;
    montar(c, html`
      <dl class="datos-mcp">
        <dt>Dirección del servidor MCP</dt><dd><code id="mcp-direccion">${info.direccion}</code> <button type="button" class="btn chico" data-copiar="mcp-direccion">Copiar</button></dd>
        <dt>Clave de la presentación</dt><dd>${info.tiene ? html`Creada el ${fecha(info.creada, true)}${info.usada ? html` · usada por última vez el ${fecha(info.usada, true)}` : ' · todavía sin usar'}` : 'Sin clave'}</dd>
      </dl>
      ${presentacion ? html`<div class="aviso-legal mcp-nueva" role="status">
        <p><b>Copie la clave ahora: no se vuelve a mostrar.</b> Va en la cabecera <code>Authorization: Bearer …</code> del cliente MCP. Si el cliente solo acepta una dirección, use la segunda (lleva la clave: guárdela como un secreto).</p>
        <div class="mcp-copiar"><label class="campo"><span>Clave</span><input id="mcp-clave" readonly value="${presentacion.clave}"></label><button type="button" class="btn" data-copiar="mcp-clave">Copiar</button></div>
        <div class="mcp-copiar"><label class="campo"><span>Dirección con la clave</span><input id="mcp-con-clave" readonly value="${presentacion.direccion_con_clave}"></label><button type="button" class="btn" data-copiar="mcp-con-clave">Copiar</button></div>
      </div>` : ''}
      <div class="fila-botones">
        <button type="button" class="btn ${info.tiene ? '' : 'primario'}" id="mcp-crear">${info.tiene ? 'Crear otra clave' : 'Crear clave'}</button>
        ${info.tiene ? html`<button type="button" class="btn" id="mcp-revocar">Revocar la clave</button>` : ''}
        <a class="btn" href="${url('/presentacion?off=1')}" target="_blank" rel="noopener">Abrir la pantalla en off</a>
      </div>
      ${conDatos(info) ? pintarDatos(info, datos) : ''}`);
    if (conDatos(info)) cargarPropuestas();
  }

  async function cargarMcp() {
    try { pintarMcp(await api.get('/api/pantalla/clave')); } catch (e) {
      const c = $('#mcp', el);
      if (c?.isConnected) montar(c, html`<p class="sec">${e.message}</p>`);
    }
  }

  // Una propuesta pendiente: la tarjeta entera (cada valor como se va a escribir), el motivo que dio el agente, de qué
  // clave, desde qué IP y cuándo llegó y vence. Sin «aprobar todas»: cada una se lee y se decide sola.
  function pintarPropuesta(p) {
    const enCurso = p.estado === 'en_curso';
    return html`<article class="mcp-propuesta" id="propuesta-${p.id}" data-estado="${p.estado}">
      <p class="mcp-propuesta-et">${p.etiqueta || p.herramienta}</p>
      <h4>${p.titulo || 'Propuesta del agente'}</h4>
      ${p.motivo ? html`<p class="mcp-motivo"><b>Por qué lo propone el agente:</b> ${p.motivo}</p>` : ''}
      <dl>${(p.detalle || []).map(([k, v]) => html`<div><dt>${k}</dt><dd>${v}</dd></div>`)}</dl>
      ${p.aviso ? html`<p class="mcp-propuesta-aviso">${p.aviso}</p>` : ''}
      <p class="sec mcp-origen">Llegó el ${fecha(p.creada, true)} desde ${p.ip || '—'} con la clave ${p.clave?.huella || '—'}${p.clave?.creada ? html` (creada el ${fecha(p.clave.creada, true)})` : ''} · vence el ${fecha(p.vence, true)}</p>
      ${enCurso ? html`<p class="mcp-propuesta-estado">Guardándose…</p>` : html`<div class="fila-botones">
        <button type="button" class="btn primario" data-aprobar="${p.id}">Aprobar</button>
        <button type="button" class="btn" data-rechazar="${p.id}">Rechazar</button>
      </div>`}
    </article>`;
  }

  async function cargarPropuestas() {
    const c = $('#mcp-propuestas', el);
    if (!c?.isConnected) return;
    let d;
    try { d = await api.get('/api/mcp/propuestas'); } catch (e) {
      if (c.isConnected) montar(c, html`<p class="sec">${e.message}</p>`);
      return;
    }
    if (!c.isConnected) return;
    const lista = d.propuestas || [];
    const recientes = d.recientes || [];
    montar(c, html`
      <h3>Cambios que propone el agente${lista.length ? html` <span class="chip ambar">${lista.length}</span>` : ''}</h3>
      ${lista.length ? html`<div class="mcp-propuestas">${lista.map(pintarPropuesta)}</div>` : html`<p class="sec">No hay cambios esperando su aprobación.</p>`}
      ${recientes.length ? html`<details class="mcp-recientes"><summary>Últimas decididas</summary><ul>${recientes.map((p) => html`<li><b>${ESTADOS[p.estado] || p.estado}</b> · ${p.etiqueta || p.herramienta} · ${fecha(p.decidida_en, true)}${p.resumen ? html` · ${p.resumen}` : ''}${p.error?.mensaje ? html` · ${p.error.mensaje}` : ''}</li>`)}</ul></details>` : ''}`);
    if (propuestaPedida) {
      const pedida = c.querySelector(`#propuesta-${CSS.escape(propuestaPedida)}`);
      if (pedida) {
        pedida.classList.add('resaltada');
        pedida.scrollIntoView({ block: 'center' });
      } else {
        aviso('Esa propuesta ya no espera su aprobación: mire las últimas decididas.', 'error', 6000);
      }
      propuestaPedida = null;
    }
  }

  async function decidir(id, aprobar, boton) {
    const tarjeta = boton.closest('.mcp-propuesta');
    for (const b of tarjeta?.querySelectorAll('button') || []) b.disabled = true;
    try {
      const r = await api.post(`/api/mcp/propuestas/${id}`, { aprobar });
      if (r.estado === 'hecha') aviso(r.resumen ? `Hecho: ${r.resumen}` : 'Hecho');
      else if (r.estado === 'rechazada') aviso('Propuesta rechazada');
      else aviso(r.error?.mensaje || 'No se pudo hacer', 'error', 8000);
    } catch (err) { avisoError(err); }
    try { refrescarInsignias(); } catch (e) { console.error(e); }
    await cargarPropuestas();
  }

  // Tras ponerse al día, la sesión queda como la ve el servidor y se va al inicio
  async function alDia() {
    const d = await api.get('/api/yo');
    Object.assign(yo, d);
    configurar({ token: d.csrf, usuario: d.usuario, uid: d.uid, rol: d.rol, permisos: d.permisos, excepto: d.excepto,
      nombre: d.nombre, debe_cambiar_clave: d.debe_cambiar_clave, compromiso_pendiente: d.compromiso_pendiente });
    if (!d.debe_cambiar_clave && !d.compromiso_pendiente && pendienteAlEntrar) {
      aviso('Su cuenta está al día');
      ir(puede('tablero.ver') ? '/' : '/trabajo');
      return;
    }
    pintar();
  }

  el.addEventListener('submit', async (e) => {
    if (e.target.id !== 'f-clave') return;
    e.preventDefault();
    const f = e.target;
    const error = f.querySelector('.error');
    error.textContent = '';
    if (f.nueva.value !== f.repetida.value) { error.textContent = 'Las dos claves nuevas no coinciden'; return; }
    const boton = f.querySelector('button[type=submit]');
    boton.disabled = true;
    try {
      const r = await api.post('/api/yo/clave', { actual: f.actual.value, nueva: f.nueva.value });
      // La sesión se renovó: el CSRF es otro
      configurar({ token: r.csrf, usuario: sesion.usuario, uid: sesion.uid, rol: sesion.rol, permisos: sesion.permisos,
        excepto: sesion.excepto, nombre: sesion.nombre, debe_cambiar_clave: false, compromiso_pendiente: sesion.compromisoPendiente });
      aviso('Clave cambiada');
      await alDia();
    } catch (err) {
      if (err?.estado === 401) return;
      error.textContent = err.message;
      f.actual.value = '';
      f.actual.focus();
    } finally {
      boton.disabled = false;
    }
  });
  el.addEventListener('click', async (e) => {
    const copiar = e.target.closest('[data-copiar]');
    if (copiar) {
      const origen = $(`#${copiar.dataset.copiar}`, el);
      const texto = origen?.value ?? origen?.textContent ?? '';
      try { await navigator.clipboard.writeText(texto); aviso('Copiado'); } catch { origen?.select?.(); aviso('Selecciónelo y cópielo', 'error'); }
      return;
    }
    if (e.target.closest('#mcp-crear')) {
      const reemplaza = !!$('#mcp-revocar', el);
      if (reemplaza && !await confirmar('La clave anterior de la presentación deja de valer: el agente que la use ya no podrá manejar la pantalla.', { si: 'Crear otra' })) return;
      try { const r = await api.post('/api/pantalla/clave'); pintarMcp(r, r); } catch (err) { avisoError(err); }
      return;
    }
    if (e.target.closest('#mcp-revocar')) {
      if (!await confirmar('El agente que use la clave de la presentación ya no podrá manejar la pantalla en off.', { si: 'Revocar' })) return;
      try { const r = await api.del('/api/pantalla/clave?tipo=presentacion'); pintarMcp(r); aviso('Clave revocada'); } catch (err) { avisoError(err); }
      return;
    }
    if (e.target.closest('#mcp-crear-datos')) {
      const alcances = [...el.querySelectorAll('input[name=alcance]:checked')].map((x) => x.value);
      if (!alcances.length) { aviso('Elija al menos un permiso para la clave de datos', 'error'); return; }
      const reemplaza = !!$('#mcp-revocar-datos', el);
      const texto = (reemplaza ? 'La clave de datos anterior deja de valer y sus propuestas sin decidir se anulan. ' : '')
        + 'Lo que pida el agente con esta clave sale del panel hacia ese cliente: úsela solo para la tarea.';
      if (!await confirmar(texto, { si: reemplaza ? 'Crear otra' : 'Crear la clave' })) return;
      try { const r = await api.post('/api/pantalla/clave', { tipo: 'datos', alcances }); pintarMcp(r, r); } catch (err) { avisoError(err); }
      return;
    }
    if (e.target.closest('#mcp-revocar-datos')) {
      if (!await confirmar('El agente que use la clave de datos ya no podrá leer ni proponer nada, y sus propuestas sin decidir se anulan.', { si: 'Revocar' })) return;
      try { const r = await api.del('/api/pantalla/clave?tipo=datos'); pintarMcp(r); aviso('Clave de datos revocada'); } catch (err) { avisoError(err); }
      return;
    }
    const aprobar = e.target.closest('[data-aprobar]');
    if (aprobar) { await decidir(aprobar.dataset.aprobar, true, aprobar); return; }
    const rechazar = e.target.closest('[data-rechazar]');
    if (rechazar) { await decidir(rechazar.dataset.rechazar, false, rechazar); return; }
    if (!e.target.closest('#aceptar')) return;
    try {
      await api.post('/api/yo/compromiso', { version: yo.compromiso?.version });
      await alDia();
    } catch (err) { avisoError(err); }
  });
  pintar();
}
